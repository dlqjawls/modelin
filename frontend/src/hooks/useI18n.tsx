/**
 * Modelin - i18n (한국어/영어 전환)
 */
import { createContext, useContext, useState, type ReactNode } from 'react';

type Lang = 'ko' | 'en';

const translations = {
  ko: {
    // Navigation
    'nav.dashboard': '대시보드',
    'nav.screener': '종목 스크리닝',
    'nav.backtest': '백테스팅',
    'nav.chart': '차트 분석',
    'nav.portfolio': '포트폴리오',
    'nav.trading': '자동 매매',
    'nav.settings': '설정',
    'nav.analysis': '분석 도구',
    'nav.execution': '실행',

    // Dashboard
    'dash.title': '대시보드',
    'dash.totalAssets': '총 자산',
    'dash.todayReturn': '오늘 수익률',
    'dash.totalReturn': '총 수익률',
    'dash.activeTrades': '활성 전략',
    'dash.marketOverview': '시장 현황',
    'dash.recentActivity': '최근 활동',
    'dash.watchlist': '관심 종목',

    // Screener
    'screen.title': '종목 스크리닝',
    'screen.addCondition': '조건 추가',
    'screen.run': '스크리닝 실행',
    'screen.results': '결과',
    'screen.factor': '팩터',
    'screen.operator': '조건',
    'screen.value': '값',

    // Backtest
    'bt.title': '백테스팅',
    'bt.strategy': '전략',
    'bt.period': '기간',
    'bt.capital': '초기 자본',
    'bt.run': '백테스트 실행',
    'bt.totalReturn': '총 수익률',
    'bt.cagr': '연평균 수익률',
    'bt.sharpe': '샤프 비율',
    'bt.mdd': '최대 낙폭',
    'bt.winRate': '승률',
    'bt.trades': '총 거래',
    'bt.equityCurve': '에퀴티 커브',

    // Chart
    'chart.title': '차트 분석',
    'chart.symbol': '종목 코드',
    'chart.interval': '간격',
    'chart.indicators': '기술 지표',

    // Common
    'common.search': '종목 검색...',
    'common.loading': '로딩 중...',
    'common.noData': '데이터가 없습니다',
    'common.error': '오류가 발생했습니다',
    'common.market': '시장',
    'common.krx': '한국',
    'common.us': '미국',
    'common.crypto': '암호화폐',
    'common.comingSoon': '준비 중',
  },
  en: {
    // Navigation
    'nav.dashboard': 'Dashboard',
    'nav.screener': 'Screener',
    'nav.backtest': 'Backtest',
    'nav.chart': 'Chart Analysis',
    'nav.portfolio': 'Portfolio',
    'nav.trading': 'Auto Trading',
    'nav.settings': 'Settings',
    'nav.analysis': 'Analysis',
    'nav.execution': 'Execution',

    // Dashboard
    'dash.title': 'Dashboard',
    'dash.totalAssets': 'Total Assets',
    'dash.todayReturn': "Today's Return",
    'dash.totalReturn': 'Total Return',
    'dash.activeTrades': 'Active Strategies',
    'dash.marketOverview': 'Market Overview',
    'dash.recentActivity': 'Recent Activity',
    'dash.watchlist': 'Watchlist',

    // Screener
    'screen.title': 'Stock Screener',
    'screen.addCondition': 'Add Condition',
    'screen.run': 'Run Screener',
    'screen.results': 'Results',
    'screen.factor': 'Factor',
    'screen.operator': 'Operator',
    'screen.value': 'Value',

    // Backtest
    'bt.title': 'Backtest',
    'bt.strategy': 'Strategy',
    'bt.period': 'Period',
    'bt.capital': 'Initial Capital',
    'bt.run': 'Run Backtest',
    'bt.totalReturn': 'Total Return',
    'bt.cagr': 'CAGR',
    'bt.sharpe': 'Sharpe Ratio',
    'bt.mdd': 'Max Drawdown',
    'bt.winRate': 'Win Rate',
    'bt.trades': 'Total Trades',
    'bt.equityCurve': 'Equity Curve',

    // Chart
    'chart.title': 'Chart Analysis',
    'chart.symbol': 'Symbol',
    'chart.interval': 'Interval',
    'chart.indicators': 'Indicators',

    // Common
    'common.search': 'Search stocks...',
    'common.loading': 'Loading...',
    'common.noData': 'No data available',
    'common.error': 'An error occurred',
    'common.market': 'Market',
    'common.krx': 'Korea',
    'common.us': 'US',
    'common.crypto': 'Crypto',
    'common.comingSoon': 'Coming Soon',
  },
} as const;

type TranslationKey = keyof typeof translations.ko;

interface I18nContextType {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey) => string;
}

const I18nContext = createContext<I18nContextType | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>('ko');

  const t = (key: TranslationKey): string => {
    return translations[lang][key] || key;
  };

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n must be used within I18nProvider');
  return context;
}
