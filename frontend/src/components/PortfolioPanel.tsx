import { useState } from 'react';
import { BarChart3, Loader2 } from 'lucide-react';
import { portfolioApi, type PortfolioOptimizationResult } from '../services/api';

const methods = [['equal_weight', '동일 가중'], ['inverse_volatility', '변동성 역가중'], ['min_volatility', '최소 변동성']];

export default function PortfolioPanel() {
  const [symbols, setSymbols] = useState('005930,000660');
  const [market, setMarket] = useState('krx');
  const [method, setMethod] = useState('inverse_volatility');
  const [startDate, setStartDate] = useState('2024-01-01');
  const [endDate, setEndDate] = useState('2024-06-30');
  const [result, setResult] = useState<PortfolioOptimizationResult | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const optimize = async () => {
    const list = symbols.split(',').map((value) => value.trim()).filter(Boolean);
    if (!list.length) { setError('종목을 하나 이상 입력해주세요.'); return; }
    setLoading(true); setError('');
    try {
      const response = await portfolioApi.optimize({ symbols: list, market, method, start_date: startDate, end_date: endDate });
      setResult(response.data);
    } catch (err) { setResult(null); setError(err instanceof Error ? err.message : '최적화에 실패했습니다.'); }
    finally { setLoading(false); }
  };

  return <div className="page-content animate-fadeIn">
    <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
      <div className="card-header"><span className="card-title">포트폴리오 최적화</span><BarChart3 size={20} color="var(--accent-blue)" /></div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 'var(--space-md)' }}>
        <div className="input-group"><label className="input-label">시장</label><select className="select-field" value={market} onChange={(e) => setMarket(e.target.value)}><option value="krx">🇰🇷 KRX</option><option value="us">🇺🇸 US</option><option value="crypto">🪙 Crypto</option></select></div>
        <div className="input-group"><label className="input-label">종목 코드 (쉼표 구분)</label><input className="input-field" value={symbols} onChange={(e) => setSymbols(e.target.value)} /></div>
        <div className="input-group"><label className="input-label">배분 방법</label><select className="select-field" value={method} onChange={(e) => setMethod(e.target.value)}>{methods.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div className="input-group"><label className="input-label">시작일</label><input className="input-field" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></div>
        <div className="input-group"><label className="input-label">종료일</label><input className="input-field" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></div>
      </div>
      <button className="btn btn-primary" style={{ marginTop: 16 }} onClick={optimize} disabled={loading}>{loading ? <Loader2 size={16} /> : <BarChart3 size={16} />} 최적화 실행</button>
      {error && <p style={{ color: 'var(--color-loss)', marginTop: 12 }}>{error}</p>}
    </div>
    {result && <div className="card"><div className="card-header"><span className="card-title">권장 비중</span></div><div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>{Object.entries(result.weights).map(([symbol, weight]) => <div className="metric-card" key={symbol}><span className="metric-label">{symbol}</span><strong className="metric-value">{(weight * 100).toFixed(2)}%</strong></div>)}</div><div style={{ display: 'flex', gap: 24, marginTop: 20, color: 'var(--text-secondary)' }}><span>예상 연수익률 <b style={{ color: 'var(--color-profit)' }}>{(result.expected_return * 100).toFixed(2)}%</b></span><span>변동성 <b>{(result.expected_volatility * 100).toFixed(2)}%</b></span><span>샤프 <b>{result.sharpe_ratio.toFixed(2)}</b></span></div></div>}
  </div>;
}
