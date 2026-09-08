/**
 * Modelin - 차트 분석 페이지
 * 백엔드 API 연동 버전 (실시간 OHLCV 데이터)
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
} from 'lightweight-charts';
import { RefreshCw, Search, AlertCircle } from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import { marketApi, type OHLCVItem } from '../services/api';

const QUICK_SYMBOLS = {
  krx: [
    { symbol: '005930', name: '삼성전자' },
    { symbol: '000660', name: 'SK하이닉스' },
    { symbol: '005380', name: '현대차' },
    { symbol: '035420', name: 'NAVER' },
  ],
  us: [
    { symbol: 'NVDA', name: 'NVIDIA' },
    { symbol: 'AAPL', name: 'Apple' },
    { symbol: 'TSLA', name: 'Tesla' },
    { symbol: 'MSFT', name: 'Microsoft' },
  ],
  crypto: [
    { symbol: 'BTC/USDT', name: 'Bitcoin' },
    { symbol: 'ETH/USDT', name: 'Ethereum' },
    { symbol: 'SOL/USDT', name: 'Solana' },
  ],
};

function formatDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export default function ChartView() {
  const { t } = useI18n();
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const sma20SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const sma60SeriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  const [market, setMarket] = useState<'krx' | 'us' | 'crypto'>('krx');
  const [symbol, setSymbol] = useState('005930');
  const [inputSymbol, setInputSymbol] = useState('005930');
  const [interval, setInterval] = useState('1d');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [latestStats, setLatestStats] = useState({
    open: 0,
    high: 0,
    low: 0,
    close: 0,
    volume: 0,
    changeRate: 0,
    currency: 'KRW',
  });

  // 차트 인스턴스 초기화
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const container = chartContainerRef.current;
    container.innerHTML = '';

    const chart = createChart(container, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
      },
      crosshair: {
        vertLine: {
          color: 'rgba(59, 130, 246, 0.3)',
          labelBackgroundColor: '#3b82f6',
        },
        horzLine: {
          color: 'rgba(59, 130, 246, 0.3)',
          labelBackgroundColor: '#3b82f6',
        },
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
      },
      timeScale: {
        borderColor: 'rgba(255, 255, 255, 0.08)',
        timeVisible: true,
      },
      width: container.clientWidth,
      height: 480,
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    const sma20Series = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 1,
      title: 'SMA 20',
    });

    const sma60Series = chart.addSeries(LineSeries, {
      color: '#f59e0b',
      lineWidth: 1,
      title: 'SMA 60',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries as any;
    sma20SeriesRef.current = sma20Series as any;
    sma60SeriesRef.current = sma60Series as any;
    volumeSeriesRef.current = volumeSeries as any;

    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  // 실제 백엔드 API에서 OHLCV 조회
  const fetchChartData = useCallback(async () => {
    if (!symbol) return;
    setLoading(true);
    setError(null);

    const now = new Date();
    const oneYearAgo = new Date();
    oneYearAgo.setDate(now.getDate() - 365);

    const start = formatDate(oneYearAgo);
    const end = formatDate(now);

    try {
      const res = await marketApi.getOHLCV(symbol, market, start, end, interval);
      const data: OHLCVItem[] = res.data;

      if (!data || data.length === 0) {
        setError(`${symbol} (${market.toUpperCase()})에 대한 가격 데이터를 찾을 수 없습니다.`);
        setLoading(false);
        return;
      }

      // 날짜순 정렬 및 중복 제거
      const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
      const seen = new Set<string>();
      const uniqueData = sorted.filter((d) => {
        if (seen.has(d.date)) return false;
        seen.add(d.date);
        return true;
      });

      const candlePoints = uniqueData.map((d) => ({
        time: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));

      // SMA 20 계산
      const sma20 = uniqueData
        .map((_, i, arr) => {
          if (i < 19) return null;
          const sum = arr.slice(i - 19, i + 1).reduce((acc, cur) => acc + cur.close, 0);
          return { time: arr[i].date, value: sum / 20 };
        })
        .filter(Boolean) as { time: string; value: number }[];

      // SMA 60 계산
      const sma60 = uniqueData
        .map((_, i, arr) => {
          if (i < 59) return null;
          const sum = arr.slice(i - 59, i + 1).reduce((acc, cur) => acc + cur.close, 0);
          return { time: arr[i].date, value: sum / 60 };
        })
        .filter(Boolean) as { time: string; value: number }[];

      // 거래량 데이터
      const volData = uniqueData.map((d) => ({
        time: d.date,
        value: d.volume,
        color: d.close >= d.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
      }));

      if (candleSeriesRef.current) candleSeriesRef.current.setData(candlePoints);
      if (sma20SeriesRef.current) sma20SeriesRef.current.setData(sma20);
      if (sma60SeriesRef.current) sma60SeriesRef.current.setData(sma60);
      if (volumeSeriesRef.current) volumeSeriesRef.current.setData(volData);

      if (chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }

      // 최신 봉 정보 업데이트
      const latest = uniqueData[uniqueData.length - 1];
      const prev = uniqueData.length > 1 ? uniqueData[uniqueData.length - 2] : null;
      const chgRate = prev && prev.close > 0 ? ((latest.close - prev.close) / prev.close) * 100 : 0;

      setLatestStats({
        open: latest.open,
        high: latest.high,
        low: latest.low,
        close: latest.close,
        volume: latest.volume,
        changeRate: chgRate,
        currency: market === 'krx' ? 'KRW' : 'USD',
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '데이터 조회 중 오류가 발생했습니다.';
      setError(`API 연결 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [symbol, market, interval]);

  useEffect(() => {
    fetchChartData();
  }, [fetchChartData]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputSymbol.trim()) {
      setSymbol(inputSymbol.trim());
    }
  };

  const handleMarketChange = (newMarket: 'krx' | 'us' | 'crypto') => {
    setMarket(newMarket);
    const defaultSym = QUICK_SYMBOLS[newMarket][0]?.symbol || '';
    setSymbol(defaultSym);
    setInputSymbol(defaultSym);
  };

  const formatPrice = (val: number) => {
    if (latestStats.currency === 'KRW') {
      return `₩${val.toLocaleString()}`;
    }
    return `$${val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div className="page-content animate-fadeIn">
      {/* Controls Bar */}
      <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-md)',
            flexWrap: 'wrap',
          }}
        >
          {/* Market Selector */}
          <div className="input-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <label className="input-label" style={{ whiteSpace: 'nowrap' }}>
              {t('common.market')}
            </label>
            <select
              className="select-field"
              value={market}
              onChange={(e) => handleMarketChange(e.target.value as 'krx' | 'us' | 'crypto')}
            >
              <option value="krx">🇰🇷 KRX</option>
              <option value="us">🇺🇸 US</option>
              <option value="crypto">🪙 Crypto</option>
            </select>
          </div>

          {/* Symbol Input */}
          <form onSubmit={handleSearchSubmit} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <div className="input-group" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <label className="input-label" style={{ whiteSpace: 'nowrap' }}>
                {t('chart.symbol')}
              </label>
              <input
                className="input-field"
                value={inputSymbol}
                onChange={(e) => setInputSymbol(e.target.value)}
                placeholder="005930, AAPL..."
                style={{ width: 130 }}
              />
            </div>
            <button type="submit" className="btn btn-sm btn-ghost" title="조회">
              <Search size={14} />
            </button>
          </form>

          {/* Quick Select Buttons */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {QUICK_SYMBOLS[market].map((q) => (
              <button
                key={q.symbol}
                className={`btn btn-sm ${symbol === q.symbol ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => {
                  setSymbol(q.symbol);
                  setInputSymbol(q.symbol);
                }}
                style={{ fontSize: '0.75rem', padding: '3px 8px' }}
              >
                {q.name}
              </button>
            ))}
          </div>

          {/* Interval Buttons */}
          <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
            {['1d', '1w', '1M'].map((int) => (
              <button
                key={int}
                className={`btn btn-sm ${interval === int ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setInterval(int)}
              >
                {int}
              </button>
            ))}
            <button
              className="btn btn-sm btn-ghost"
              onClick={fetchChartData}
              disabled={loading}
              title="새로고침"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            </button>
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
          <button
            className="btn btn-sm btn-ghost"
            style={{ marginLeft: 'auto', color: '#f87171' }}
            onClick={fetchChartData}
          >
            다시 시도
          </button>
        </div>
      )}

      {/* Chart Canvas */}
      <div className="card" style={{ padding: 0, overflow: 'hidden', position: 'relative' }}>
        {loading && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(10, 14, 23, 0.65)',
              zIndex: 10,
              backdropFilter: 'blur(2px)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--accent-blue)' }}>
              <RefreshCw size={20} className="animate-spin" />
              <span>실시간 주가 데이터 로딩 중...</span>
            </div>
          </div>
        )}
        <div ref={chartContainerRef} style={{ width: '100%', height: 480 }} />
      </div>

      {/* Live Stat Bar */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: 'var(--space-md)',
          marginTop: 'var(--space-md)',
        }}
      >
        <div className="stat-card blue">
          <div className="stat-label">현재/종가</div>
          <div className="stat-value" style={{ fontSize: '1.05rem', color: 'var(--text-primary)' }}>
            {latestStats.close ? formatPrice(latestStats.close) : '-'}
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label">등락률</div>
          <div
            className="stat-value"
            style={{
              fontSize: '1.05rem',
              color: latestStats.changeRate >= 0 ? 'var(--color-profit)' : 'var(--color-loss)',
            }}
          >
            {latestStats.changeRate >= 0 ? '+' : ''}
            {latestStats.changeRate.toFixed(2)}%
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label">시가</div>
          <div className="stat-value" style={{ fontSize: '1.05rem', color: 'var(--text-primary)' }}>
            {latestStats.open ? formatPrice(latestStats.open) : '-'}
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label">고가</div>
          <div className="stat-value" style={{ fontSize: '1.05rem', color: 'var(--color-profit)' }}>
            {latestStats.high ? formatPrice(latestStats.high) : '-'}
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label">저가</div>
          <div className="stat-value" style={{ fontSize: '1.05rem', color: 'var(--color-loss)' }}>
            {latestStats.low ? formatPrice(latestStats.low) : '-'}
          </div>
        </div>

        <div className="stat-card blue">
          <div className="stat-label">거래량</div>
          <div className="stat-value" style={{ fontSize: '1.05rem', color: 'var(--accent-cyan)' }}>
            {latestStats.volume ? latestStats.volume.toLocaleString() : '-'}
          </div>
        </div>
      </div>
    </div>
  );
}
