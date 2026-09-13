/**
 * Modelin - 퀀트 투자 플랫폼
 *
 * 메인 앱 컴포넌트. 사이드바 네비게이션 + 페이지 라우팅.
 */
import { useState } from 'react';
import Sidebar from './components/Sidebar';
import HeaderBar from './components/HeaderBar';
import Dashboard from './components/Dashboard';
import ScreenerPanel from './components/ScreenerPanel';
import BacktestPanel from './components/BacktestPanel';
import ChartView from './components/ChartView';
import TradingPanel from './components/TradingPanel';
import PortfolioPanel from './components/PortfolioPanel';
import SettingsPanel from './components/SettingsPanel';

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
        {renderPage()}
      </main>
    </div>
  );
}
