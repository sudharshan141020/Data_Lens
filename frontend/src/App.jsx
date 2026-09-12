import { useState, useEffect, useMemo, useRef } from 'react';
import Sidebar from './components/Sidebar';
import MappingSummary from './components/MappingSummary';
import UploadZone from './components/UploadZone';
import ExecutiveSummary from './components/ExecutiveSummary';
import IntelligentDashboard from './components/IntelligentDashboard';
import StoryMode from './components/StoryMode';
import AnalysisExplorerV2 from './components/AnalysisExplorerV2';
import FindingsPanel from './components/FindingsPanel';
import WeakPointsPanel from './components/WeakPointsPanel';
import DataQualityCenter from './components/DataQualityCenter';
import CorrelationCenter from './components/CorrelationCenter';
import SegmentsPanel from './components/SegmentsPanel';
import SeasonalityPanel from './components/SeasonalityPanel';
import PeriodComparisonPanel from './components/PeriodComparisonPanel';
import AnomaliesPanel from './components/AnomaliesPanel';
import SimpsonsParadoxPanel from './components/SimpsonsParadoxPanel';
import BenfordPanel from './components/BenfordPanel';
import WorkflowSteps from './components/WorkflowSteps';
import TopBar from './components/TopBar';
import ExportMenu from './components/ExportMenu';
import FilterBar from './components/FilterBar';
import SearchBar from './components/SearchBar';
import SampleGallery from './components/SampleGallery';
import { analyzeFile, analyzeCombined, compareFiles, downloadCleanedCsv, loadSampleFile, exportPdf } from './api';
import { exportAnalysisToExcel } from './exportReport';
import { buildFindingsText } from './findingsText';
import CompareView from './components/CompareView';
import { applyFilters, recomputeAnalysis } from './filterUtils';
import { buildSearchIndex } from './searchUtils';

function makeId() {
  return (crypto.randomUUID && crypto.randomUUID()) || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

// Pinned sessions first (most-recently-pinned first within that group),
// then everyone else in upload order.
function sortSessions(sessions) {
  const pinned = sessions.filter((s) => s.pinned);
  const rest = sessions.filter((s) => !s.pinned);
  return [...pinned, ...rest];
}

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [combineMode, setCombineMode] = useState(false);
  const [selectedForCombine, setSelectedForCombine] = useState([]);
  const [compareMode, setCompareMode] = useState(false);
  const [selectedForCompare, setSelectedForCompare] = useState([]);
  const [sampleLoadingId, setSampleLoadingId] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState(null);
  const [filters, setFilters] = useState(null);
  const [jumpTarget, setJumpTarget] = useState(null);
  const jumpNonceRef = useRef(0);

  const handleJumpToAnalysis = (analysisId) => {
    jumpNonceRef.current += 1;
    setJumpTarget({ id: analysisId, nonce: jumpNonceRef.current });
  };

  useEffect(() => {
    setFilters(null); // a filter set for one dataset's columns doesn't apply to another
  }, [activeId]);

  const handleFilesSelected = (files, errorMsg) => {
    setUploadError(errorMsg || null);
    if (!files.length) return;

    const newSessions = files.map((file) => ({
      id: makeId(),
      fileName: file.name,
      status: 'loading',
      result: null,
      error: null,
      pinned: false,
      sourceFile: file, // kept in memory so this file can be resent later for combining
      isCombined: false,
    }));

    setSessions((prev) => [...prev, ...newSessions]);
    setActiveId(newSessions[0].id);

    files.forEach((file, idx) => {
      const sessionId = newSessions[idx].id;
      analyzeFile(file)
        .then((data) => {
          setSessions((prev) => prev.map((s) => (
            s.id === sessionId ? { ...s, status: 'ready', result: data } : s
          )));
        })
        .catch((e) => {
          setSessions((prev) => prev.map((s) => (
            s.id === sessionId ? { ...s, status: 'error', error: e.message } : s
          )));
        });
    });
  };

  const [remappingId, setRemappingId] = useState(null);
  const [remapError, setRemapError] = useState(null);

  const handleRemapColumn = (sessionId, legacyRole, newColumn) => {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session?.sourceFile) return; // combined sessions have no single source file to resend

    const nextOverrides = { ...(session.columnOverrides || {}), [legacyRole]: newColumn };
    setRemapError(null);
    setRemappingId(sessionId);

    analyzeFile(session.sourceFile, nextOverrides)
      .then((data) => {
        setSessions((prev) => prev.map((s) => (
          s.id === sessionId ? { ...s, result: data, columnOverrides: nextOverrides } : s
        )));
      })
      .catch((e) => setRemapError(e.message || 'Could not apply that column mapping.'))
      .finally(() => setRemappingId(null));
  };

  const handleRemove = (id) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      if (id === activeId) {
        setActiveId(next.length ? next[next.length - 1].id : null);
      }
      return next;
    });
    setSelectedForCombine((prev) => prev.filter((sid) => sid !== id));
  };

  const handleTogglePin = (id) => {
    setSessions((prev) => prev.map((s) => (
      s.id === id ? { ...s, pinned: !s.pinned } : s
    )));
  };

  const handleExportPdf = async (session) => {
    setPdfError(null);
    setPdfLoading(true);
    try {
      await exportPdf(session.fileName, session.result.v2);
    } catch (err) {
      setPdfError(err.message || 'The PDF report could not be generated.');
    } finally {
      setPdfLoading(false);
    }
  };

  const handleCopyFindings = async (session) => {
    const text = buildFindingsText(session);
    if (!text) return false;
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      return false;
    }
  };

  const handleDownloadCleanedCsv = async (session) => {
    if (!session?.sourceFile) throw new Error('No source file available for this session.');
    await downloadCleanedCsv(session.sourceFile, session.fileName);
  };

  const handleToggleCombineMode = () => {
    setCombineMode((m) => !m);
    setSelectedForCombine([]);
  };

  const handleToggleSelect = (id) => {
    setSelectedForCombine((prev) => (
      prev.includes(id) ? prev.filter((sid) => sid !== id) : [...prev, id]
    ));
  };

  const handleCombine = () => {
    const chosen = sessions.filter((s) => (
      selectedForCombine.includes(s.id) && s.status === 'ready' && s.sourceFile
    ));
    if (chosen.length < 2) return;

    const combinedId = makeId();
    const combinedName = `Combined: ${chosen.map((s) => s.fileName).join(' + ')}`;

    setSessions((prev) => [...prev, {
      id: combinedId,
      fileName: combinedName,
      status: 'loading',
      result: null,
      error: null,
      pinned: false,
      sourceFile: null,
      isCombined: true,
    }]);
    setActiveId(combinedId);
    setCombineMode(false);
    setSelectedForCombine([]);

    analyzeCombined(chosen.map((s) => s.sourceFile))
      .then((data) => {
        setSessions((prev) => prev.map((s) => (
          s.id === combinedId ? { ...s, status: 'ready', result: data } : s
        )));
      })
      .catch((e) => {
        setSessions((prev) => prev.map((s) => (
          s.id === combinedId ? { ...s, status: 'error', error: e.message } : s
        )));
      });
  };

  const handleToggleCompareMode = () => {
    setCompareMode((m) => !m);
    setSelectedForCompare([]);
  };

  const handleToggleSelectForCompare = (id) => {
    setSelectedForCompare((prev) => {
      if (prev.includes(id)) return prev.filter((sid) => sid !== id);
      if (prev.length >= 2) return prev; // capped at exactly two
      return [...prev, id];
    });
  };

  const handleCompare = () => {
    const chosen = sessions.filter((s) => (
      selectedForCompare.includes(s.id) && s.status === 'ready' && s.sourceFile
    ));
    if (chosen.length !== 2) return;

    const compareId = makeId();
    const compareName = `Compare: ${chosen[0].fileName} vs ${chosen[1].fileName}`;

    setSessions((prev) => [...prev, {
      id: compareId,
      fileName: compareName,
      status: 'loading',
      result: null,
      error: null,
      pinned: false,
      sourceFile: null,
      isComparison: true,
    }]);
    setActiveId(compareId);
    setCompareMode(false);
    setSelectedForCompare([]);

    compareFiles(chosen[0].sourceFile, chosen[1].sourceFile)
      .then((data) => {
        setSessions((prev) => prev.map((s) => (
          s.id === compareId ? { ...s, status: 'ready', result: data } : s
        )));
      })
      .catch((e) => {
        setSessions((prev) => prev.map((s) => (
          s.id === compareId ? { ...s, status: 'error', error: e.message } : s
        )));
      });
  };

  const handleTrySample = (sample) => {
    setSampleLoadingId(sample.id);
    loadSampleFile(sample.filename)
      .then((file) => handleFilesSelected([file], null))
      .catch((e) => setUploadError(e.message))
      .finally(() => setSampleLoadingId(null));
  };

  const displaySessions = sortSessions(sessions);
  const activeSession = sessions.find((s) => s.id === activeId);

  const filterableData = activeSession?.result?.v2?.filterable_data;
  const hasActiveFilters = !!(filters && (
    filters.dateFrom || filters.dateTo ||
    Object.values(filters.dimensionFilters || {}).some((s) => s && s.size > 0)
  ));

  const filteredRows = useMemo(() => {
    if (!filterableData?.available) return [];
    if (!hasActiveFilters) return filterableData.rows;
    return applyFilters(filterableData.rows, filters);
  }, [filterableData, filters, hasActiveFilters]);

  const displayedTopAnalyses = useMemo(() => {
    const raw = activeSession?.result?.v2?.top_analyses || [];
    if (!hasActiveFilters) return raw;
    return raw.map((a) => recomputeAnalysis(a, filteredRows));
  }, [activeSession, hasActiveFilters, filteredRows]);

  const displayedAllAnalyses = useMemo(() => {
    const raw = activeSession?.result?.v2?.all_analyses || [];
    if (!hasActiveFilters) return raw;
    return raw.map((a) => recomputeAnalysis(a, filteredRows));
  }, [activeSession, hasActiveFilters, filteredRows]);

  const searchIndex = useMemo(() => {
    if (!activeSession?.result?.v2) return [];
    return buildSearchIndex(activeSession.result.v2);
  }, [activeSession]);

  return (
    <div className="app-shell">
      <TopBar />

      {sessions.length > 0 && (
        <Sidebar
          sessions={displaySessions}
          activeId={activeId}
          onSelect={setActiveId}
          onRemove={handleRemove}
          onFilesSelected={handleFilesSelected}
          uploadError={uploadError}
          onTogglePin={handleTogglePin}
          combineMode={combineMode}
          onToggleCombineMode={handleToggleCombineMode}
          selectedForCombine={selectedForCombine}
          onToggleSelect={handleToggleSelect}
          onCombine={handleCombine}
          compareMode={compareMode}
          onToggleCompareMode={handleToggleCompareMode}
          selectedForCompare={selectedForCompare}
          onToggleSelectForCompare={handleToggleSelectForCompare}
          onCompare={handleCompare}
        />
      )}

      <main className={`app-main-area ${sessions.length === 0 ? 'centered' : ''}`}>
        {sessions.length === 0 && (
          <div className="empty-state">
            <div className="hero">
              <div className="brand">
                <span className="brand-mark" />
                <span className="brand-name">DATALENS</span>
              </div>
              <p className="hero-kicker">Automated Data Intelligence</p>
              <p className="hero-desc">
                Upload any Excel, CSV, JSON, or Parquet file and instantly surface trends,
                correlations, outliers, and concrete recommendations — ranked
                by how much they actually matter. Works on any dataset;
                sales files unlock deeper findings like profit risk and
                customer concentration automatically.
              </p>
            </div>

            <UploadZone onFilesSelected={handleFilesSelected} error={uploadError} />

            <SampleGallery onTrySample={handleTrySample} loadingId={sampleLoadingId} />

            <WorkflowSteps />

            <ul className="trust-list">
              <li>✓ Automatic column detection — works on files it's never seen</li>
              <li>✓ Rule-based, ranked findings — no AI calls, nothing sent to third parties</li>
              <li>✓ Nothing stored — each file is processed in memory and discarded</li>
            </ul>

            <p className="tech-line dim-sub">
              Powered by <span className="mono">React • FastAPI • Python • pandas</span>
            </p>
          </div>
        )}

        {activeSession && activeSession.status === 'loading' && (
          <div className="session-loading">
            <p className="upload-title">
              {activeSession.isCombined ? 'Combining files…' : activeSession.isComparison ? 'Comparing files…' : `Reading ${activeSession.fileName}…`}
            </p>
            <p className="dim-sub">Detecting columns, computing KPIs, ranking findings</p>
          </div>
        )}

        {activeSession && activeSession.status === 'error' && (
          <div className="session-loading">
            <p className="upload-title" style={{ color: 'var(--red)' }}>Couldn't analyze {activeSession.fileName}</p>
            <p className="dim-sub">{activeSession.error}</p>
          </div>
        )}

        {activeSession && activeSession.status === 'ready' && activeSession.isComparison && (
          <CompareView data={activeSession.result} />
        )}

        {activeSession && activeSession.status === 'ready' && !activeSession.isComparison && (
          <div className="dashboard">
            {activeSession.isCombined && (
              <p className="dim-sub" style={{ marginBottom: 12 }}>
                Merged from {activeSession.result.source_files?.join(', ')}
              </p>
            )}

            <div className="export-row">
              <ExportMenu
                onExportExcel={() => exportAnalysisToExcel(activeSession)}
                onExportPdf={() => handleExportPdf(activeSession)}
                onCopyFindings={() => handleCopyFindings(activeSession)}
                onDownloadCleanedCsv={activeSession.sourceFile ? () => handleDownloadCleanedCsv(activeSession) : null}
                pdfLoading={pdfLoading}
              />
            </div>
            {pdfError && <p className="export-error">{pdfError}</p>}

            <ExecutiveSummary fileName={activeSession.fileName} v2={activeSession.result.v2} />

            <MappingSummary
              result={activeSession.result}
              onRemap={(role, col) => handleRemapColumn(activeSession.id, role, col)}
              remapping={remappingId === activeSession.id}
              remapError={remapError}
            />

            <SearchBar index={searchIndex} onJumpToAnalysis={handleJumpToAnalysis} />

            <FilterBar
              filterableData={filterableData}
              filters={filters}
              onChange={setFilters}
              filteredCount={filteredRows.length}
              totalCount={filterableData?.rows?.length || 0}
            />

            <IntelligentDashboard topAnalyses={displayedTopAnalyses} tickNum="02" filtersActive={hasActiveFilters} />

            <StoryMode story={activeSession.result.v2.story} tickNum="03" />

            <div className="dashboard-grid">
              <AnalysisExplorerV2 analyses={displayedAllAnalyses} tickNum="04" filtersActive={hasActiveFilters} jumpTarget={jumpTarget} />
              <FindingsPanel findings={activeSession.result.v2.findings} tickNum="05" />
              <WeakPointsPanel weakPoints={activeSession.result.v2.weak_points} tickNum="06" />
              <DataQualityCenter dataQuality={activeSession.result.v2.data_quality} tickNum="07" />
              <CorrelationCenter correlationCenter={activeSession.result.v2.correlation_center} tickNum="08" />
              <SegmentsPanel segments={activeSession.result.v2.segments} tickNum="09" />
              <SeasonalityPanel seasonality={activeSession.result.v2.seasonality} tickNum="10" />
              <PeriodComparisonPanel periodComparison={activeSession.result.v2.period_comparison} tickNum="11" />
              <AnomaliesPanel anomalies={activeSession.result.v2.anomalies} tickNum="12" />
              <SimpsonsParadoxPanel simpsonsParadox={activeSession.result.v2.simpsons_paradox} tickNum="13" />
              <BenfordPanel benford={activeSession.result.v2.benford} tickNum="14" />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
