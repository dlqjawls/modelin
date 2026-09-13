import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Settings } from 'lucide-react';
import { getApiErrorMessage, healthCheck } from '../services/client';
import { operationsApi } from '../services/operations';
import type { DiagnosticsResponse, HealthResponse, LiveDiagnosticsResponse } from '../contracts/operations';

export default function SettingsPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [live, setLive] = useState<LiveDiagnosticsResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try { const [healthResponse, diagnosticResponse] = await Promise.all([healthCheck(), operationsApi.diagnostics()]); setHealth(healthResponse.data); setDiagnostics(diagnosticResponse.data); }
    catch (cause) { setError(getApiErrorMessage(cause, '진단 정보를 불러오지 못했습니다.')); }
    finally { setLoading(false); }
  }, []);
  const runLiveCheck = async () => {
    setLoading(true); setError('');
    try { const response = await operationsApi.liveDiagnostics(); setLive(response.data); }
    catch (cause) { setError(getApiErrorMessage(cause, '실시간 진단에 실패했습니다.')); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [refresh]);
  return <div className="page-content animate-fadeIn">
    <div className="page-header"><div><h2>시스템 설정 및 연결 진단</h2><p>API 키 자체는 표시하지 않고 연결 상태만 확인합니다.</p></div><div style={{ display: 'flex', gap: 8 }}><button className="btn btn-secondary" onClick={() => void refresh()} disabled={loading}><RefreshCw size={16} /> 새로고침</button><button className="btn btn-primary" onClick={() => void runLiveCheck()} disabled={loading}>실시간 연결 확인</button></div></div>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="dashboard-grid">
      <section className="card"><div className="card-header"><span className="card-title">서버 상태</span><Settings size={18} color="var(--accent-blue)" /></div><div className="metric-row"><span>API</span><strong>{health?.status ?? '확인 중'}</strong></div><div className="metric-row"><span>Paper worker</span><strong>{health?.paper_worker ?? '-'}</strong></div></section>
      <section className="card"><div className="card-header"><span className="card-title">데이터·브로커 연결</span></div>{Object.entries(diagnostics?.sources ?? {}).map(([name, state]) => <div className="metric-row" key={name}><span>{name}</span><strong>{String(state)}</strong></div>)}<div className="metric-row"><span>실거래</span><strong>{diagnostics?.live_trading ?? '-'}</strong></div><div className="metric-row"><span>코인 매매</span><strong>{diagnostics?.crypto_trading ?? '-'}</strong></div></section>
      <section className="card"><div className="card-header"><span className="card-title">실시간 조회 결과</span></div>{live ? Object.entries(live).map(([name, value]) => <div className="metric-row" key={name}><span>{name}</span><strong>{value.status}</strong></div>) : <p style={{ color: 'var(--text-tertiary)' }}>버튼을 눌러 읽기 전용 연결을 확인하세요.</p>}</section>
    </div>
  </div>;
}
