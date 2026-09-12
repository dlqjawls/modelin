import { useCallback, useEffect, useState } from 'react';
import { Activity, RefreshCw } from 'lucide-react';
import { healthCheck, operationsApi, type PaperAccount } from '../services/api';

export default function TradingPanel() {
  const [accounts, setAccounts] = useState<PaperAccount[]>([]);
  const [selected, setSelected] = useState<PaperAccount | null>(null);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workerState, setWorkerState] = useState('unknown');

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const response = await operationsApi.accounts();
      const health = await healthCheck();
      setWorkerState(health.data.paper_worker ?? 'unknown');
      setAccounts(response.data);
      setSelected((current) => current && response.data.find((item) => item.id === current.id) || response.data[0] || null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '운영 상태를 불러오지 못했습니다.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!selected) { setSnapshot(null); return; }
    void operationsApi.snapshot(selected.id)
      .then((response) => setSnapshot(response.data))
      .catch((cause) => setError(cause instanceof Error ? cause.message : '계좌 snapshot을 불러오지 못했습니다.'));
  }, [selected]);

  return <div className="page-content">
    <div className="page-header"><div><h2>자동매매 운영</h2><p>현재는 안전한 Paper 모드만 지원합니다.</p></div>
      <span className={`badge ${workerState === 'running' ? 'badge-success' : 'badge-info'}`}>WORKER · {workerState.toUpperCase()}</span>
      <button className="btn btn-secondary" onClick={() => void refresh()}><RefreshCw size={16} /> 새로고침</button></div>
    {error && <div className="alert alert-error">{error}</div>}
    {loading ? <div className="empty-state">계좌 상태를 불러오는 중...</div> : !accounts.length ?
      <div className="empty-state"><Activity size={42} /><h3>Paper 계좌가 없습니다</h3><p>백엔드 API에서 Paper 계좌를 생성하면 여기에 표시됩니다.</p></div> :
      <div className="dashboard-grid">
        <section className="card"><h3>계좌</h3>{accounts.map((account) => <button key={account.id}
          className={`list-row ${selected?.id === account.id ? 'active' : ''}`} onClick={() => setSelected(account)}>
          <span>{account.name}</span><span className="badge badge-info">PAPER · {account.market.toUpperCase()}</span></button>)}</section>
        <section className="card"><h3>계좌 스냅샷</h3><div className="metric-row"><span>현금</span><strong>{snapshot?.snapshot?.cash ?? '-'}</strong></div>
          <div className="metric-row"><span>보유 종목</span><strong>{snapshot?.snapshot?.positions?.length ?? 0}</strong></div>
          <div className="metric-row"><span>주문 이벤트</span><strong>{snapshot?.snapshot?.events?.length ?? 0}</strong></div>
        </section>
      </div>}
  </div>;
}
