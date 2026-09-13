/**
 * Modelin - 종목 스크리닝 패널
 * 백엔드 API 실시간 연동 버전
 */
import { useState, useCallback, useEffect } from 'react';
import { Plus, X, Play, Download, RefreshCw, AlertCircle, Sparkles } from 'lucide-react';
import { useI18n } from '../hooks/useI18n';
import {
  screenerApi,
  type ScreenerCondition,
  type ScreenerResultItem,
} from '../services/research';

interface UIExtendedCondition {
  id: number;
  factor: string;
  operator: string;
  value: string;
}

const FACTORS = [
  { value: 'per', label: 'PER (주가수익비율)' },
  { value: 'pbr', label: 'PBR (주가순자산비율)' },
  { value: 'roe', label: 'ROE (자기자본이익률 %)' },
  { value: 'eps', label: 'EPS (주당순이익)' },
  { value: 'bps', label: 'BPS (주당순자산)' },
  { value: 'dividend_yield', label: '배당수익률 (%)' },
  { value: 'market_cap', label: '시가총액' },
];

const OPERATORS = ['<', '<=', '>', '>=', '==', '!='];

const PRESETS = [
  {
    name: '저평가 가치주',
    conditions: [
      { id: 1, factor: 'per', operator: '<', value: '15' },
      { id: 2, factor: 'pbr', operator: '<', value: '1.5' },
      { id: 3, factor: 'roe', operator: '>', value: '5' },
    ],
  },
  {
    name: '고배당 매력주',
    conditions: [
      { id: 1, factor: 'dividend_yield', operator: '>', value: '2.5' },
      { id: 2, factor: 'pbr', operator: '<', value: '1.2' },
    ],
  },
  {
    name: '고성장 우량주',
    conditions: [
      { id: 1, factor: 'roe', operator: '>', value: '12' },
      { id: 2, factor: 'per', operator: '<', value: '30' },
    ],
  },
];

function formatMarketCap(val: number): string {
  if (!val) return '-';
  if (val >= 1_000_000_000_000) {
    return `${(val / 1_000_000_000_000).toFixed(1)}조`;
  }
  if (val >= 100_000_000) {
    return `${(val / 100_000_000).toFixed(0)}억`;
  }
  return val.toLocaleString();
}

export default function ScreenerPanel() {
  const { t } = useI18n();
  const [market, setMarket] = useState('krx');
  const [conditions, setConditions] = useState<UIExtendedCondition[]>([
    { id: 1, factor: 'per', operator: '<', value: '18' },
    { id: 2, factor: 'pbr', operator: '<', value: '2.5' },
  ]);
  const [nextId, setNextId] = useState(3);

  const [results, setResults] = useState<ScreenerResultItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const addCondition = () => {
    setConditions([
      ...conditions,
      { id: nextId, factor: 'per', operator: '<', value: '10' },
    ]);
    setNextId(nextId + 1);
  };

  const removeCondition = (id: number) => {
    setConditions(conditions.filter((c) => c.id !== id));
  };

  const updateCondition = (id: number, field: keyof UIExtendedCondition, value: string) => {
    setConditions(
      conditions.map((c) => (c.id === id ? { ...c, [field]: value } : c))
    );
  };

  const applyPreset = (presetConditions: UIExtendedCondition[]) => {
    setConditions(presetConditions);
  };

  // 백엔드 API 스크리닝 실행
  const runScreening = useCallback(async () => {
    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const parsedConditions: ScreenerCondition[] = conditions
        .filter((c) => c.value.trim() !== '' && !isNaN(Number(c.value)))
        .map((c) => ({
          factor: c.factor,
          operator: c.operator,
          value: parseFloat(c.value),
        }));

      const res = await screenerApi.run(market, parsedConditions, 'market_cap', 50);
      const data = res.data;

      setResults(data.results || []);
      setTotalCount(data.total_count || 0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '스크리닝 중 오류가 발생했습니다.';
      setError(`스크리닝 실패: ${msg}`);
      setResults([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [market, conditions]);

  // 최초 로드시 1회 자동 실행
  useEffect(() => {
    void runScreening();
  }, [runScreening]);

  // CSV 다운로드
  const exportCSV = () => {
    if (results.length === 0) return;
    const header = '종목코드,종목명,시장,PER,PBR,ROE,EPS,BPS,배당수익률,시가총액,섹터\n';
    const rows = results
      .map((r) =>
        [
          r.symbol,
          `"${r.name}"`,
          r.market,
          r.per ?? '',
          r.pbr ?? '',
          r.roe ?? '',
          r.eps ?? '',
          r.bps ?? '',
          r.dividend_yield ?? '',
          r.market_cap ?? '',
          `"${r.sector || ''}"`,
        ].join(',')
      )
      .join('\n');

    const blob = new Blob(['\uFEFF' + header + rows], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `screener_${market}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-content animate-fadeIn">
      {/* Condition Builder Card */}
      <div className="card" style={{ marginBottom: 'var(--space-md)' }}>
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className="card-title">{t('screen.title')}</span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-tertiary)' }}>
              (실시간 팩터 기반 스크리너)
            </span>
          </div>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <select
              className="select-field"
              value={market}
              onChange={(e) => setMarket(e.target.value)}
            >
              <option value="krx">🇰🇷 {t('common.krx')}</option>
              <option value="us">🇺🇸 {t('common.us')}</option>
              <option value="crypto">🪙 {t('common.crypto')}</option>
            </select>
          </div>
        </div>

        {/* Preset Strategies */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginBottom: 'var(--space-md)',
            flexWrap: 'wrap',
          }}
        >
          <span style={{ fontSize: '0.8rem', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 4 }}>
            <Sparkles size={13} style={{ color: 'var(--accent-cyan)' }} />
            추천 프리셋:
          </span>
          {PRESETS.map((p) => (
            <button
              key={p.name}
              className="btn btn-sm btn-ghost"
              onClick={() => applyPreset(p.conditions)}
              style={{ fontSize: '0.75rem', padding: '3px 10px', borderRadius: 20 }}
            >
              {p.name}
            </button>
          ))}
        </div>

        {/* Condition Rows */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {conditions.map((cond) => (
            <div
              key={cond.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '8px 12px',
                background: 'var(--bg-tertiary)',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-subtle)',
                flexWrap: 'wrap',
              }}
            >
              <select
                className="select-field"
                value={cond.factor}
                onChange={(e) => updateCondition(cond.id, 'factor', e.target.value)}
                style={{ width: 190 }}
              >
                {FACTORS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>

              <select
                className="select-field"
                value={cond.operator}
                onChange={(e) => updateCondition(cond.id, 'operator', e.target.value)}
                style={{ width: 70 }}
              >
                {OPERATORS.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>

              <input
                className="input-field"
                type="number"
                step="any"
                value={cond.value}
                onChange={(e) => updateCondition(cond.id, 'value', e.target.value)}
                placeholder="값 입력 (예: 15)"
                style={{ width: 140 }}
              />

              <button
                className="btn btn-sm btn-ghost"
                onClick={() => removeCondition(cond.id)}
                disabled={conditions.length <= 1}
                title="조건 삭제"
                style={{ color: 'var(--text-tertiary)' }}
              >
                <X size={16} />
              </button>
            </div>
          ))}
        </div>

        {/* Action Buttons */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 'var(--space-md)',
          }}
        >
          <button className="btn btn-secondary btn-sm" onClick={addCondition}>
            <Plus size={14} />
            {t('screen.addCondition')}
          </button>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              className="btn btn-primary"
              onClick={runScreening}
              disabled={loading}
              style={{ minWidth: 120 }}
            >
              {loading ? (
                <>
                  <RefreshCw size={15} className="animate-spin" />
                  스크리닝 중...
                </>
              ) : (
                <>
                  <Play size={15} />
                  {t('screen.run')}
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error Message */}
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
            onClick={runScreening}
          >
            다시 시도
          </button>
        </div>
      )}

      {/* Results Card */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="card-title">{t('screen.results')}</span>
            <span className="badge badge-info" style={{ fontSize: '0.75rem' }}>
              {totalCount}개 종목 통과
            </span>
          </div>

          <button
            className="btn btn-sm btn-ghost"
            onClick={exportCSV}
            disabled={results.length === 0}
            title="CSV 내보내기"
          >
            <Download size={14} />
            CSV 다운로드
          </button>
        </div>

        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>종목코드</th>
                <th>종목명</th>
                <th style={{ textAlign: 'right' }}>PER</th>
                <th style={{ textAlign: 'right' }}>PBR</th>
                <th style={{ textAlign: 'right' }}>ROE</th>
                <th style={{ textAlign: 'right' }}>EPS</th>
                <th style={{ textAlign: 'right' }}>배당수익률</th>
                <th style={{ textAlign: 'right' }}>시가총액</th>
                <th>시장/섹터</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '40px 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 10, color: 'var(--accent-blue)' }}>
                      <RefreshCw size={20} className="animate-spin" />
                      <span>팩터 데이터 분석 및 스크리닝 진행 중...</span>
                    </div>
                  </td>
                </tr>
              ) : results.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-tertiary)' }}>
                    {hasSearched ? '조건을 만족하는 종목이 없습니다. 조건을 완화해 보세요.' : '스크리닝 조건을 설정하고 실행해 보세요.'}
                  </td>
                </tr>
              ) : (
                results.map((r) => (
                  <tr key={r.symbol}>
                    <td>
                      <span style={{ fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                        {r.symbol}
                      </span>
                    </td>
                    <td>
                      <strong>{r.name}</strong>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {r.per !== null && r.per !== undefined ? r.per.toFixed(2) : '-'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {r.pbr !== null && r.pbr !== undefined ? r.pbr.toFixed(2) : '-'}
                    </td>
                    <td
                      style={{
                        textAlign: 'right',
                        color: r.roe && r.roe >= 10 ? 'var(--color-profit)' : 'inherit',
                      }}
                    >
                      {r.roe !== null && r.roe !== undefined ? `${r.roe.toFixed(1)}%` : '-'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {r.eps ? `₩${Math.round(r.eps).toLocaleString()}` : '-'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {r.dividend_yield !== null && r.dividend_yield !== undefined ? `${r.dividend_yield.toFixed(2)}%` : '-'}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--text-secondary)' }}>
                      {formatMarketCap(r.market_cap)}
                    </td>
                    <td>
                      <span className="badge badge-warning" style={{ fontSize: '0.72rem' }}>
                        {r.sector || r.market.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
