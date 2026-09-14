/* oxlint-disable react/set-state-in-effect -- async dashboard loading synchronizes external API state */
/**
 * Modelin - Dashboard 페이지
 * 백엔드 API 연동 버전
 */
import { useState, useEffect, useCallback } from 'react';
import {
  TrendingUp,
  Wallet,
  BarChart3,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  RefreshCw,
} from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { marketApi, type AssetInfo } from '../services/research';
import { operationsApi } from '../services/operations';

interface WatchlistItem extends AssetInfo {
  price: number;
  change: number;
}

function formatKRW(value: number): string {
  if (value >= 100000000) return `${(value / 100000000).toFixed(1)}억`;
  if (value >= 10000) return `${(value / 10000).toFixed(0)}만`;
  return value.toLocaleString();
}

function formatPrice(value: number, currency: string): string {
  if (currency === 'USD') return `$${value.toLocaleString()}`;
  return `₩${formatKRW(value)}`;
}

// 날짜 포맷 유틸
function dateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function Dashboard() {
  const { t } = useI18n();
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [equityData, setEquityData] = useState<{ date: string; value: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kisTotalAssets, setKisTotalAssets] = useState<number | null>(null);

  const fetchWatchlist = useCallback(async () => {
    const items: WatchlistItem[] = [];
    const [krxResponse, usResponse] = await Promise.allSettled([
      marketApi.getTickers('krx'),
      marketApi.getTickers('us'),
    ]);
    const krxTickers = krxResponse.status === 'fulfilled' ? krxResponse.value.data : [];
    const usTickers = usResponse.status === 'fulfilled' ? usResponse.value.data : [];
    const candidates = [
      ...krxTickers.slice(0, 2).map((item) => ({ ...item, market: 'krx' })),
      ...usTickers.slice(0, 2).map((item) => ({ ...item, market: 'us' })),
    ];

    for (const w of candidates) {
      try {
        // 종목 정보 조회
        const info = w;

        // 최근 2일 가격 데이터로 변동률 계산
        const end = new Date();
        const start = new Date();
        start.setDate(end.getDate() - 7); // 여유있게 7일

        const ohlcvRes = await marketApi.getOHLCV(
          w.symbol, w.market, dateStr(start), dateStr(end), '1d'
        );
        const ohlcv = ohlcvRes.data;

        let price = 0;
        let change = 0;
        if (ohlcv.length >= 2) {
          price = ohlcv[ohlcv.length - 1].close;
          const prevClose = ohlcv[ohlcv.length - 2].close;
          change = prevClose > 0 ? ((price - prevClose) / prevClose) * 100 : 0;
        } else if (ohlcv.length === 1) {
          price = ohlcv[0].close;
        }
        try {
          const quote = (await marketApi.getQuote(w.symbol, w.market)).data;
          if (quote.price !== null) price = quote.price;
          if (quote.change_rate !== null) change = quote.change_rate;
        } catch {
          // Historical close remains the fallback outside the KIS session.
        }

        items.push({
          ...info,
          price,
          change: Math.round(change * 100) / 100,
        });
      } catch {
        // 개별 종목 실패는 무시
      }
    }

    setWatchlist(items);
  }, []);

  const fetchEquityData = useCallback(async () => {
    // Use the KIS account valuation; do not fabricate a curve from a seed amount.
    try {
      const response = await operationsApi.kisAccount('krx');
      const total = Number(response.data.total_assets);
      setKisTotalAssets(Number.isFinite(total) ? total : null);
      setEquityData(Number.isFinite(total) ? [{ date: '현재', value: total }] : []);
    } catch {
      setKisTotalAssets(null);
      setEquityData([]);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([fetchWatchlist(), fetchEquityData()]);
    } catch {
      setError('백엔드 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.');
    } finally {
      setLoading(false);
    }
  }, [fetchWatchlist, fetchEquityData]);

  // Async loading synchronizes dashboard state with external APIs.
  // oxlint-disable-next-line react/set-state-in-effect
  useEffect(() => {
    loadData();
  }, [loadData]);

  // Total assets come from KIS, never from the watchlist sum.
  const totalAssets = kisTotalAssets ?? 0;
  const avgChange = watchlist.length > 0
    ? watchlist.reduce((sum, w) => sum + w.change, 0) / watchlist.length
    : 0;

  return (
    <div className="page-content animate-fadeIn">
      {/* Error Banner */}
      {error && (
        <div
          style={{
            padding: 'var(--space-md)',
            background: 'var(--color-warning-bg)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            borderRadius: 'var(--radius-md)',
            color: 'var(--color-warning)',
            fontSize: '0.85rem',
            marginBottom: 'var(--space-md)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>⚠️ {error}</span>
          <button className="btn btn-sm btn-ghost" onClick={loadData}>
            <RefreshCw size={14} /> 재시도
          </button>
        </div>
      )}

      {/* Stat Cards */}
      <div className="stats-grid">
        <div className="stat-card blue">
          <div className="stat-icon blue"><Wallet size={20} /></div>
          <div className="stat-label">{t('dash.totalAssets')}</div>
          <div className="stat-value" style={{ color: 'var(--text-primary)' }}>
            {loading ? '...' : kisTotalAssets === null ? '-' : `₩${totalAssets.toLocaleString()}`}
          </div>
        </div>

        <div className="stat-card green">
          <div className="stat-icon green"><TrendingUp size={20} /></div>
          <div className="stat-label">{t('dash.todayReturn')}</div>
          <div className="stat-value" style={{
            color: avgChange >= 0 ? 'var(--color-profit)' : 'var(--color-loss)'
          }}>
            {loading ? '...' : `${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}%`}
          </div>
        </div>

        <div className="stat-card purple">
          <div className="stat-icon purple"><BarChart3 size={20} /></div>
          <div className="stat-label">{t('dash.totalReturn')}</div>
          <div className="stat-value" style={{ color: 'var(--accent-purple)' }}>
            {loading ? '...' : (equityData.length > 1
              ? `${((equityData[equityData.length - 1].value / equityData[0].value - 1) * 100).toFixed(1)}%`
              : '-')}
          </div>
        </div>

        <div className="stat-card cyan">
          <div className="stat-icon cyan"><Zap size={20} /></div>
          <div className="stat-label">{t('dash.activeTrades')}</div>
          <div className="stat-value" style={{ color: 'var(--accent-cyan)' }}>0</div>
          <div style={{ marginTop: 4 }}>
            <span className="badge badge-info">Paper Trading</span>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="content-grid" style={{ marginTop: 'var(--space-md)' }}>
        {/* Equity Curve */}
        <div className="card wide">
          <div className="card-header">
            <span className="card-title">{t('bt.equityCurve')}</span>
            <button className="btn btn-sm btn-ghost" onClick={loadData}>
              <RefreshCw size={14} />
            </button>
          </div>
          <div style={{ height: 300, position: 'relative' }}>
            {loading && (
              <div className="loading-overlay">
                <div className="loading-spinner" />
              </div>
            )}
            {equityData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityData}>
                  <defs>
                    <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={{ stroke: 'rgba(255,255,255,0.06)' }} tickLine={false} interval={14} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} width={60} />
                  <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '10px', color: '#f1f5f9', fontSize: '0.8rem', fontFamily: "'JetBrains Mono', monospace" }} formatter={(value: any) => [`₩${Number(value || 0).toLocaleString()}`, '자산']} />
                  <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fill="url(#equityGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : !loading ? (
              <div className="empty-state">
                <Activity size={48} className="empty-state-icon" />
                <h3>{t('common.noData')}</h3>
                <p>백엔드 서버를 실행하면 실시간 데이터가 표시됩니다.</p>
              </div>
            ) : null}
          </div>
        </div>

        {/* Watchlist */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">{t('dash.watchlist')}</span>
            <button className="btn btn-sm btn-ghost" onClick={fetchWatchlist}>
              <RefreshCw size={14} />
            </button>
          </div>
          <div style={{ overflowY: 'auto', maxHeight: 340, position: 'relative' }}>
            {loading && (
              <div className="loading-overlay">
                <div className="loading-spinner" />
              </div>
            )}
            {watchlist.length > 0 ? watchlist.map((item) => (
              <div
                key={`${item.market}-${item.symbol}`}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 0', borderBottom: '1px solid var(--border-subtle)',
                  cursor: 'pointer', transition: 'background 150ms',
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{item.symbol}</span>
                    <span className="badge badge-info">{item.market.toUpperCase()}</span>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginTop: 2 }}>
                    {item.name}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: '0.9rem' }}>
                    {formatPrice(item.price, item.currency)}
                  </div>
                  <div style={{
                    fontSize: '0.75rem', fontWeight: 600,
                    color: item.change >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
                    display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 2,
                  }}>
                    {item.change >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                    {item.change >= 0 ? '+' : ''}{item.change}%
                  </div>
                </div>
              </div>
            )) : !loading ? (
              <div className="empty-state" style={{ padding: 'var(--space-lg)' }}>
                <p>서버 연결 후 관심종목이 표시됩니다.</p>
              </div>
            ) : null}
          </div>
        </div>

        {/* Recent Activity - from Supabase later */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">{t('dash.recentActivity')}</span>
          </div>
          <div className="empty-state" style={{ padding: 'var(--space-lg)' }}>
            <Activity size={32} style={{ color: 'var(--text-muted)', opacity: 0.4 }} />
            <p style={{ marginTop: 8, color: 'var(--text-tertiary)', fontSize: '0.8rem' }}>
              스크리닝, 백테스팅 실행 시 활동 기록이 여기에 표시됩니다.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
