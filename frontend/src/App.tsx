/**
 * Modelin - 퀀트 투자 플랫폼
 *
 * 메인 앱 컴포넌트. 사이드바 네비게이션 + 페이지 라우팅.
 */
import { lazy, Suspense, useState } from 'react';
import Sidebar from './components/Sidebar';
import HeaderBar from './components/HeaderBar';

function PageFallback() {
  return <div className="page-content"><div className="loading-panel" role="status">화면을 불러오는 중...</div></div>;
}

const Dashboard = lazy(() => import('./components/Dashboard'));
const ScreenerPanel = lazy(() => import('./components/ScreenerPanel'));
const BacktestPanel = lazy(() => import('./components/BacktestPanel'));
const ChartView = lazy(() => import('./components/ChartView'));
const TradingPanel = lazy(() => import('./components/TradingPanel'));
const PortfolioPanel = lazy(() => import('./components/PortfolioPanel'));
const SettingsPanel = lazy(() => import('./components/SettingsPanel'));

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const renderPage = () => {
    switch (activePage) {
      case 'dashboard':
        return <Dashboard />;
      case 'screener':
        return <ScreenerPanel />;
      case 'backtest':
        return <BacktestPanel />;
      case 'chart':
        return <ChartView />;
      case 'portfolio':
        return <PortfolioPanel />;
      case 'trading':
        return <TradingPanel />;
      case 'settings':
        return <SettingsPanel />;
      default:
        return <Dashboard />;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <main className="main-content">
        <HeaderBar />
        <Suspense fallback={<PageFallback />}>
          {renderPage()}
        </Suspense>
      </main>
    </div>
  );
}
