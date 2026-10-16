import { useId, useMemo, useState } from 'react';
import AnalysisChartV2 from './AnalysisChartV2';
import { runCustomQuery, chooseQueryChartType } from '../filterUtils';

const AGG_LABELS = { sum: 'Total', avg: 'Average', count: 'Count of records' };

export default function QueryBuilderPanel({ filterableData, rows, tickNum }) {
  // Each <label> must be tied to its <select> (htmlFor/id), otherwise assistive
  // tech announces four unnamed dropdowns.
  const uid = useId();
  const dimensionColumns = filterableData?.dimension_columns || [];
  const measureColumns = filterableData?.measure_columns || [];

  // State holds only what the person explicitly picked. What is actually
  // used is DERIVED from it against the columns of the dataset in front of us,
  // so (a) the very first paint already shows a real result -- no effect has
  // to run before defaults appear -- and (b) switching to a dataset with
  // different columns can never leave a stale selection behind.
  const [pickedMeasure, setMeasure] = useState('');
  const [aggregation, setAggregation] = useState('sum');
  const [pickedDim1, setDim1] = useState('');
  const [pickedDim2, setDim2] = useState('');

  const measure = measureColumns.includes(pickedMeasure) ? pickedMeasure : (measureColumns[0] || '');
  const dim1 = dimensionColumns.includes(pickedDim1) ? pickedDim1 : (dimensionColumns[0] || '');
  const dim2 = pickedDim2 && pickedDim2 !== dim1 && dimensionColumns.includes(pickedDim2) ? pickedDim2 : '';

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

  // "Count of records" is already a complete phrase -- don't append "of <measure>".
  const subject = aggregation === 'count'
    ? AGG_LABELS.count
    : `${AGG_LABELS[aggregation]} of ${measure}`;
  const caption = `${subject}, by ${dim1}${dim2 ? ` × ${dim2}` : ''}`;

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
          <label htmlFor={`${uid}-agg`}>Aggregation</label>
          <select id={`${uid}-agg`} className="query-builder-select" value={aggregation} onChange={(e) => setAggregation(e.target.value)}>
            <option value="sum">Total</option>
            <option value="avg">Average</option>
            <option value="count">Count of records</option>
          </select>
        </div>

        {aggregation !== 'count' && (
          <div className="query-builder-field">
            <label htmlFor={`${uid}-measure`}>Of</label>
            <select id={`${uid}-measure`} className="query-builder-select" value={measure} onChange={(e) => setMeasure(e.target.value)}>
              {measureColumns.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        )}

        <div className="query-builder-field">
          <label htmlFor={`${uid}-dim1`}>Broken down by</label>
          <select id={`${uid}-dim1`} className="query-builder-select" value={dim1} onChange={(e) => {
            const next = e.target.value;
            setDim1(next);
            // The second dimension can't also be the first -- a column cross-tabbed
            // against itself is meaningless, and its dropdown already hides that option.
            if (next === pickedDim2) setDim2('');
          }}>
            {dimensionColumns.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        {dimensionColumns.length > 1 && (
          <div className="query-builder-field">
            <label htmlFor={`${uid}-dim2`}>And by (optional)</label>
            <select id={`${uid}-dim2`} className="query-builder-select" value={dim2} onChange={(e) => setDim2(e.target.value)}>
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
