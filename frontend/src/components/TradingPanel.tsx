/* oxlint-disable react/set-state-in-effect -- async account loading synchronizes external API state */
import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { getApiErrorMessage } from '../services/errors';
import { operationsApi } from '../services/operations';
import type { DiagnosticsResponse, LiveDiagnosticsResponse, PaperAccount, AccountSnapshotResponse, Deployment } from '../contracts/operations';

export default function TradingPanel() {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [selected, setSelected] = useState<PaperAccount | null>(null);
  const [snapshot, setSnapshot] = useState<AccountSnapshotResponse | null>(null);
  const [kisSnapshot, setKisSnapshot] = useState<{ cash: string; total_assets: string; source: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workerState, setWorkerState] = useState('unknown');
  const [workerDeploymentId, setWorkerDeploymentId] = useState<string | null>(null);
  const [lastWorkerResult, setLastWorkerResult] = useState<{ error?: string | null; result?: Record<string, unknown> | null } | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResponse | null>(null);
  const [liveDiagnostics, setLiveDiagnostics] = useState<LiveDiagnosticsResponse | null>(null);
  const [deployments, setDeployments] = useState<Deployment[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await operationsApi.accounts();
      const health = await operationsApi.health();
      setWorkerState(health.data.paper_worker ?? 'unknown');
      setWorkerDeploymentId(health.data.paper_worker_deployment_id ?? null);
      setLastWorkerResult(health.data.paper_worker_last_result ?? null);
      const [diagnosticResponse, liveDiagnosticResponse] = await Promise.allSettled([
        operationsApi.diagnostics(),
        operationsApi.liveDiagnostics(),
      ]);
      if (diagnosticResponse.status === 'fulfilled') setDiagnostics(diagnosticResponse.value.data);
      if (liveDiagnosticResponse.status === 'fulfilled') setLiveDiagnostics(liveDiagnosticResponse.value.data);
      const deploymentResponse = await operationsApi.deployments();
      setDeployments(deploymentResponse.data);
      setAccounts(response.data);
      setSelected((current) => current && response.data.find((item) => item.id === current.id) || response.data[0] || null);
    } catch (cause) {
      setError(getApiErrorMessage(cause, '운영 상태를 불러오지 못했습니다.'));
    } finally { setLoading(false); }
  }, []);
  const deployment = selected && deployments.find((item) => item.account_id === selected.id);
  const sendCommand = async (type: 'START' | 'PAUSE' | 'CANCEL_OPEN' | 'LIQUIDATE' | 'RESUME') => {
    if (!deployment) return;
    try { await operationsApi.command(deployment.id, type); await refresh(); }
    catch (cause) { setError(getApiErrorMessage(cause, '운영 명령을 처리하지 못했습니다.')); }
  };

  // Async refresh synchronizes this view with the external API.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => { void refresh(); }, [refresh]);
  // The selected account changes which external snapshots are displayed.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => {
    if (!selected) { setSnapshot(null); setKisSnapshot(null); return; }
    const controller = new AbortController();
    const accountId = selected.id;
    void operationsApi.snapshot(selected.id, { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setSnapshot(response.data);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(getApiErrorMessage(cause, `${accountId} snapshot을 불러오지 못했습니다.`));
      });
    void operationsApi.kisAccount(selected.market === 'us' ? 'us' : 'krx')
      .then((response) => {
        if (!controller.signal.aborted) setKisSnapshot(response.data);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setKisSnapshot(null);
          setError(getApiErrorMessage(cause, 'KIS 계좌 잔고를 조회하지 못했습니다.'));
        }
      });
    return () => controller.abort();
  }, [selected]);

  return <div className="page-content">
    <div className="page-header"><div><h2>자동매매 운영</h2><p>현재는 안전한 Paper 모드만 지원합니다.</p></div>
      <span className={`badge ${workerState === 'running' ? 'badge-success' : workerState === 'degraded' ? 'badge-danger' : 'badge-info'}`}>WORKER · {workerState.toUpperCase()}</span>
      <button className="btn btn-secondary" onClick={() => void refresh()}><RefreshCw size={16} /> 새로고침</button></div>
    {error && <div className="alert alert-error">{error}</div>}
    {workerDeploymentId && <div className="metric-row" style={{ marginBottom: 16 }}><span>워커 배포</span><strong>{workerDeploymentId}</strong></div>}
    {lastWorkerResult && <section className="card" style={{ marginBottom: 16 }}>
      <h3>최근 Worker 상태</h3>
      <div className="metric-row"><span>결과</span><strong>{String(lastWorkerResult.result?.status ?? (lastWorkerResult.error ? 'error' : 'unknown'))}</strong></div>
      {Boolean(lastWorkerResult.result?.reason) && <div className="metric-row"><span>사유</span><strong>{String(lastWorkerResult.result?.reason)}</strong></div>}
      {lastWorkerResult.error && <div className="alert alert-error" style={{ marginTop: 12 }}>{String(lastWorkerResult.error)}</div>}
    </section>}
    {diagnostics && <section className="card" style={{ marginBottom: 16 }}><h3>연결 진단</h3>
      <div className="metric-row"><span>Paper 운영 허용 시장</span><strong>{diagnostics.paper_allowed_markets.map((market) => market.toUpperCase()).join(', ') || '없음'}</strong></div>
      {Object.entries(diagnostics.sources || {}).map(([name, state]) => <div className="metric-row" key={name}>
        <span>{name}</span><strong>{String(state)}</strong>
      </div>)}
      {liveDiagnostics && Object.entries(liveDiagnostics).map(([name, state]) => <div className="metric-row" key={`live-${name}`}>
        <span>{name} 실시간 확인{state.error ? ` · ${state.error}` : ''}</span><strong className={state.status === 'ok' ? 'status-ok' : 'status-error'}>{state.status}</strong>
      </div>)}
      <div className="metric-row"><span>코인 매매</span><strong>{diagnostics.crypto_trading}</strong></div>
      <div className="metric-row"><span>실거래</span><strong>{diagnostics.live_trading}</strong></div>
    </section>}
    {loading ? <div className="empty-state">계좌 상태를 불러오는 중...</div> : !accounts.length ?
      <div className="empty-state"><Activity size={42} /><h3>Paper 계좌가 없습니다</h3><p>백엔드 API에서 Paper 계좌를 생성하면 여기에 표시됩니다.</p></div> :
      <div className="dashboard-grid">
        <section className="card"><h3>계좌</h3>{accounts.map((account) => <button key={account.id}
          className={`list-row ${selected?.id === account.id ? 'active' : ''}`} onClick={() => setSelected(account)}>
          <span>{account.name}</span><span className="badge badge-info">PAPER · {account.market.toUpperCase()}</span></button>)}</section>
        <section className="card"><h3>로컬 Paper 계좌 스냅샷</h3><div className="metric-row"><span>현금</span><strong>{snapshot?.snapshot?.cash ?? '-'}</strong></div>
          <div className="metric-row"><span>보유 종목</span><strong>{snapshot?.snapshot?.positions?.length ?? 0}</strong></div>
          <div className="metric-row"><span>주문 이벤트</span><strong>{snapshot?.snapshot?.events?.length ?? 0}</strong></div>
          {deployment && <><div className="metric-row"><span>전략 상태</span><strong>{deployment.observed_state}</strong></div>
            {deployment.last_error && <div className="alert alert-error" style={{ marginTop: 12 }}>{deployment.last_error}</div>}
            <div className="button-row" style={{ marginTop: 16, gap: 8 }}>
              {deployment.observed_state === 'RUNNING' ? <button className="btn btn-secondary" onClick={() => void sendCommand('PAUSE')}>일시정지</button> : <button className="btn btn-primary" onClick={() => void sendCommand('RESUME')}>재개</button>}
              <button className="btn btn-secondary" onClick={() => void sendCommand('CANCEL_OPEN')}>신규 주문 중단</button>
              <button className="btn btn-danger" onClick={() => void sendCommand('LIQUIDATE')}>전체 청산</button>
            </div></>}
        </section>
        <section className="card"><h3>KIS 모의계좌 잔고</h3>
          <div className="metric-row"><span>현금</span><strong>{kisSnapshot?.cash ?? '조회 실패'}</strong></div>
          <div className="metric-row"><span>총 평가금액</span><strong>{kisSnapshot?.total_assets ?? '조회 실패'}</strong></div>
          <div className="metric-row"><span>조회 출처</span><strong>{kisSnapshot?.source ?? 'KIS 연결 확인 필요'}</strong></div>
        </section>
      </div>}
  </div>;
}
