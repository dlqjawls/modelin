/* oxlint-disable react/set-state-in-effect -- async backtest loading synchronizes external API state */
/**
 * Modelin - 백테스팅 패널
 * 백엔드 API 실시간 연동 버전
 */
import { useState, useCallback, useEffect } from 'react';
import { Play, RotateCcw, RefreshCw, AlertCircle, TrendingUp } from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  ReferenceLine,
} from 'recharts';
import {
  backtestApi,
  type BacktestConfig,
  type BacktestResult,
  type StrategyScore,
} from '../services/research';

const STRATEGIES = [
  { value: 'equal_weight', label: '동일 가중 (Buy & Hold)' },
  { value: 'momentum', label: '모멘텀 전략' },
  { value: 'moving_average', label: '이동평균 교차 (Golden Cross)' },
  { value: 'rsi', label: 'RSI 역추세' },
  { value: 'bollinger_bands', label: '볼린저 밴드' },
];

function dateInputValue(date: Date): string {
  return date.toISOString().slice(0, 10);
}

const today = new Date();
const yearAgo = new Date(today);
yearAgo.setFullYear(today.getFullYear() - 1);

export default function BacktestPanel() {
  const { t } = useI18n();
  const [strategy, setStrategy] = useState('equal_weight');
  const [symbols, setSymbols] = useState('');
  const [market, setMarket] = useState('krx');
  const [startDate, setStartDate] = useState(dateInputValue(yearAgo));
  const [endDate, setEndDate] = useState(dateInputValue(today));
  const [capital, setCapital] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [comparison, setComparison] = useState<StrategyScore[]>([]);
  const [comparing, setComparing] = useState(false);

  // 백엔드 백테스팅 실행
  const runBacktest = useCallback(async () => {
    const symbolList = symbols
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    if (symbolList.length === 0) {
      setError('종목 코드를 1개 이상 입력해주세요.');
      return;
    }
    const initialCapital = parseFloat(capital);
    if (!Number.isFinite(initialCapital) || initialCapital <= 0) {
      setError('초기 자본금을 실제 금액으로 입력해주세요.');
      return;
    }

    setLoading(true);
    setError(null);

    const config: BacktestConfig = {
      symbols: symbolList,
      market,
      start_date: startDate,
      end_date: endDate,
      strategy: { type: strategy },
      initial_capital: initialCapital,
      commission_rate: 0.00015,
      slippage_rate: 0.001,
      rebalance_period: '1M',
    };

    try {
      const res = await backtestApi.run(config);
      setResult(res.data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '백테스팅 중 오류가 발생했습니다.';
      setError(`백테스팅 실행 실패: ${msg}`);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [symbols, market, startDate, endDate, strategy, capital]);

  const compareStrategies = useCallback(async () => {
    const symbolList = symbols.split(',').map((s) => s.trim()).filter(Boolean);
    if (!symbolList.length) { setError('종목 코드를 1개 이상 입력해주세요.'); return; }
    setComparing(true); setError(null);
    try {
      const response = await backtestApi.compare({ symbols: symbolList, market, start_date: startDate, end_date: endDate, initial_capital: parseFloat(capital) || 10_000_000 });
      setComparison(response.data);
    } catch (err: unknown) {
      setComparison([]);
      setError(`전략 비교 실패: ${err instanceof Error ? err.message : '알 수 없는 오류'}`);
    } finally { setComparing(false); }
  }, [symbols, market, startDate, endDate, capital]);

  // 최초 로드 시 1회 기본 백테스트 실행
  // Async execution synchronizes the panel with the backtest API.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => {
    void runBacktest();
  }, [runBacktest]);

  // 성과 지표 가공
  const metrics = result
    ? [
        {
          label: t('bt.totalReturn'),
          value: `${result.total_return >= 0 ? '+' : ''}${(result.total_return * 100).toFixed(2)}%`,
          color: result.total_return >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
        },
        {
          label: t('bt.cagr'),
          value: `${(result.cagr * 100).toFixed(2)}%`,
          color: result.cagr >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
        },
        {
          label: t('bt.sharpe'),
          value: result.sharpe_ratio.toFixed(2),
          color: 'var(--accent-blue)',
        },
        {
          label: 'Sortino',
          value: result.sortino_ratio.toFixed(2),
          color: 'var(--accent-blue)',
        },
        {
          label: t('bt.mdd'),
          value: `${(result.max_drawdown * 100).toFixed(2)}%`,
          color: 'var(--color-loss)',
        },
        {
          label: t('bt.winRate'),
          value: `${(result.win_rate * 100).toFixed(1)}%`,
          color: 'var(--accent-cyan)',
        },
        {
          label: '손익비',
          value: result.profit_loss_ratio.toFixed(2),
          color: 'var(--accent-purple)',
        },
        {
          label: t('bt.trades'),
          value: String(result.total_trades),
          color: 'var(--text-secondary)',
        },
      ]
    : [];

  // 에쿼티 커브 데이터 포맷팅
  const equityData = result?.equity_curve || [];

  // 월별 수익률 포맷팅
  const monthlyData = (result?.monthly_returns || []).map((m: { date: string; return: number }) => ({
    month: m.date,
    return: +(m.return * 100).toFixed(2),
  }));

  const resetForm = () => {
    setStrategy('equal_weight');
    setSymbols('005930, 000660');
    setStartDate('2024-01-01');
    setEndDate('2024-06-30');
    setCapital('10000000');
  };

  return (
    <div className="page-content animate-fadeIn">
      {/* Config Card */}
      <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="card-title">{t('bt.title')}</span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
              (벡터화 백테스팅 엔진 연동)
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <select
              className="select-field"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
            >
              <option value="krx">🇰🇷 KRX</option>
              <option value="us">🇺🇸 US</option>
              <option value="crypto">🪙 Crypto</option>
            </select>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 'var(--space-md)',
          }}
        >
          <div className="input-group">
            <label className="input-label">{t('bt.strategy')}</label>
            <select
              className="select-field"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value)}
            >
              {STRATEGIES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          <div className="input-group">
            <label className="input-label">종목 코드 (쉼표 구분)</label>
            <input
              className="input-field"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="005930, 000660"
            />
          </div>

          <div className="input-group">
            <label className="input-label">시작일</label>
            <input
              type="date"
              className="input-field"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label className="input-label">종료일</label>
            <input
              type="date"
              className="input-field"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>

          <div className="input-group">
            <label className="input-label">{t('bt.capital')} (₩)</label>
            <input
              type="number"
              className="input-field"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
            />
          </div>

          <div className="input-group" style={{ justifyContent: 'flex-end', alignSelf: 'flex-end' }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-secondary" onClick={resetForm} disabled={loading}>
                <RotateCcw size={14} /> 초기화
              </button>
              <button className="btn btn-primary" onClick={runBacktest} disabled={loading} style={{ minWidth: 120 }}>
                {loading ? (
                  <>
                    <RefreshCw size={14} className="animate-spin" />
                    계산 중...
                  </>
                ) : (
                  <>
                    <Play size={14} /> {t('bt.run')}
                  </>
                )}
              </button>
              <button className="btn btn-secondary" onClick={compareStrategies} disabled={comparing}>
                {comparing ? '비교 중...' : '전략 비교'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div
          className="card"
          style={{
            marginBottom: 'var(--space-md)',
            background: 'rgba(239, 68, 68, 0.1)',
            borderColor: 'rgba(239, 68, 68, 0.3)',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            color: '#f87171',
          }}
        >
          <AlertCircle size={18} />
          <span style={{ fontSize: '0.85rem' }}>{error}</span>
        </div>
      )}

      {comparison.length > 0 && (
        <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
          <div className="card-header"><span className="card-title">검증 구간 전략 순위</span><span style={{ color: 'var(--text-tertiary)', fontSize: '0.8rem' }}>최고 전략을 자동 적용하지 않음</span></div>
          <div style={{ overflowX: 'auto' }}><table className="data-table"><thead><tr><th>순위</th><th>전략</th><th>CAGR</th><th>샤프</th><th>최대낙폭</th><th>거래 수</th></tr></thead><tbody>{comparison.map((item, index) => <tr key={`${JSON.stringify(item.strategy)}-${index}`}><td>{index + 1}</td><td>{String(item.strategy.type || 'unknown')}</td><td>{(item.cagr * 100).toFixed(2)}%</td><td>{item.sharpe_ratio.toFixed(2)}</td><td>{(item.max_drawdown * 100).toFixed(2)}%</td><td>{item.total_trades}</td></tr>)}</tbody></table></div>
        </div>
      )}

      {/* Loading Overlay State */}
      {loading && !result && (
        <div
          className="card"
          style={{
            padding: '60px 0',
            textAlign: 'center',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 12,
            color: 'var(--accent-blue)',
          }}
        >
          <RefreshCw size={28} className="animate-spin" />
          <span style={{ fontSize: '0.95rem' }}>
            선택된 종목의 과거 주가 데이터 수집 및 퀀트 백테스팅 계산 중...
          </span>
        </div>
      )}

      {/* Results View */}
      {result && (
        <>
          {/* Metrics Grid */}
          <div className="stats-grid" style={{ marginBottom: 'var(--space-md)' }}>
            {metrics.map((m) => (
              <div key={m.label} className="stat-card blue">
                <div className="stat-label">{m.label}</div>
                <div
                  className="stat-value"
                  style={{ color: m.color, fontSize: '1.25rem' }}
                >
                  {m.value}
                </div>
              </div>
            ))}
          </div>

          <div className="content-grid">
            {/* Equity Curve Chart */}
            <div className="card wide">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={16} style={{ color: 'var(--accent-blue)' }} />
                  <span className="card-title">{t('bt.equityCurve')} (자산 변화)</span>
                </div>
                <div style={{ display: 'flex', gap: 12, fontSize: '0.75rem' }}>
                  <span style={{ color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span
                      style={{
                        width: 12,
                        height: 3,
                        background: 'var(--accent-blue)',
                        borderRadius: 2,
                        display: 'inline-block',
                      }}
                    />
                    포트폴리오 평가액
                  </span>
                </div>
              </div>

              <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityData}>
                    <defs>
                      <linearGradient id="strategyGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: '#64748b', fontSize: 10 }}
                      axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      dataKey="value"
                      tick={{ fill: '#64748b', fontSize: 10 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`}
                      width={55}
                      domain={['dataMin - 500000', 'dataMax + 500000']}
                    />
                    <Tooltip
                      contentStyle={{
                        background: '#1a2235',
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '10px',
                        color: '#f1f5f9',
                        fontSize: '0.75rem',
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                      formatter={(v: any) => [`₩${Math.round(Number(v) || 0).toLocaleString()}`, '평가액']}
                    />
                    <Area
                      type="monotone"
                      dataKey="value"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      fill="url(#strategyGrad)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Monthly Returns Bar Chart */}
            <div className="card">
              <div className="card-header">
                <span className="card-title">월별 수익률 (%)</span>
              </div>
              <div style={{ height: 320 }}>
                {monthlyData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={monthlyData}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                      <XAxis
                        dataKey="month"
                        tick={{ fill: '#64748b', fontSize: 10 }}
                        axisLine={{ stroke: 'rgba(255,255,255,0.06)' }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: '#64748b', fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v) => `${v}%`}
                        width={45}
                      />
                      <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" />
                      <Tooltip
                        contentStyle={{
                          background: '#1a2235',
                          border: '1px solid rgba(255,255,255,0.1)',
                          borderRadius: '10px',
                          color: '#f1f5f9',
                          fontSize: '0.75rem',
                          fontFamily: "'JetBrains Mono', monospace",
                        }}
                        formatter={(v: any) => [`${Number(v) >= 0 ? '+' : ''}${v}%`, '수익률']}
                      />
                      <Bar dataKey="return" radius={[3, 3, 0, 0]}>
                        {monthlyData.map((entry, idx) => (
                          <Cell
                            key={`cell-${idx}`}
                            fill={entry.return >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      height: '100%',
                      color: 'var(--text-tertiary)',
                      fontSize: '0.85rem',
                    }}
                  >
                    데이터가 충분하지 않습니다.
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
