import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Settings } from 'lucide-react';
import { getApiErrorMessage } from '../services/errors';
import { operationsApi } from '../services/operations';
import type { DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse } from '../contracts/operations';
import { PageHeader, StatusBadge } from './ui';

export default function SettingsPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [live, setLive] = useState<LiveDiagnosticsResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try { const [healthResponse, diagnosticResponse] = await Promise.all([operationsApi.health(), operationsApi.diagnostics()]); setHealth(healthResponse.data); setDiagnostics(diagnosticResponse.data); }
    catch (cause) { setError(getApiErrorMessage(cause, '진단 정보를 불러오지 못했습니다.')); }
    finally { setLoading(false); }
  }, []);
  const runLiveCheck = async () => {
    setLoading(true); setError('');
    try { const response = await operationsApi.liveDiagnostics(); setLive(response.data); }
    catch (cause) { setError(getApiErrorMessage(cause, '실시간 진단에 실패했습니다.')); }
    finally { setLoading(false); }
  };
  // Async refresh synchronizes this view with the external API.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void refresh(); }, [refresh]);
  const sourceEntries = Object.entries(diagnostics?.sources ?? {});
  const liveEntries = live ? Object.entries(live) : [];
  return <div className="page-content animate-fadeIn">
    <PageHeader title="시스템 설정 및 연결 진단" description="API 키 자체는 표시하지 않고 연결 상태만 확인합니다." actions={<><button className="btn btn-secondary" onClick={() => void refresh()} disabled={loading}><RefreshCw size={16} /> 새로고침</button><button className="btn btn-primary" onClick={() => void runLiveCheck()} disabled={loading}>실시간 연결 확인</button></>} />
    {error && <div className="alert alert-error">{error}</div>}
    <div className="dashboard-grid">
      <section className="card"><div className="card-header"><span className="card-title">서버 상태</span><Settings size={18} color="var(--accent-blue)" /></div><div className="metric-row"><span>API</span><StatusBadge label={health?.status ?? '확인 중'} tone={health?.status === 'ok' ? 'success' : 'neutral'} /></div><div className="metric-row"><span>Paper worker</span><StatusBadge label={health?.paper_worker ?? '-'} tone={health?.paper_worker === 'running' ? 'success' : 'neutral'} /></div></section>
      <section className="card"><div className="card-header"><span className="card-title">데이터·브로커 연결</span></div>{sourceEntries.length > 0 ? sourceEntries.map(([name, state]) => <div className="metric-row" key={name}><span>{name}</span><StatusBadge label={String(state)} tone={String(state).includes('configured') ? 'success' : 'warning'} /></div>) : <p className="muted-copy">진단 정보가 아직 없습니다.</p>}<div className="metric-row"><span>실거래</span><StatusBadge label={diagnostics?.live_trading ?? '-'} tone="neutral" /></div><div className="metric-row"><span>코인 매매</span><StatusBadge label={diagnostics?.crypto_trading ?? '-'} tone="neutral" /></div></section>
      <section className="card"><div className="card-header"><span className="card-title">실시간 조회 결과</span></div>{liveEntries.length > 0 ? liveEntries.map(([name, value]) => <div className="metric-row" key={name}><span>{name}</span><StatusBadge label={value.status} tone={value.status === 'ok' ? 'success' : 'danger'} /></div>) : <p className="muted-copy">버튼을 눌러 읽기 전용 연결을 확인하세요.</p>}</section>
    </div>
  </div>;
}
