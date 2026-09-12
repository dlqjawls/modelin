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
import { PieChart, Settings } from 'lucide-react';
import { useI18n } from './hooks/useI18n';

function ComingSoonPage({ title, icon: Icon }: { title: string; icon: React.ElementType }) {
  return (
    <div className="page-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="empty-state">
        <Icon size={64} style={{ color: 'var(--text-muted)', marginBottom: 16, opacity: 0.4 }} />
        <h3>{title}</h3>
        <p style={{ color: 'var(--text-tertiary)', marginTop: 8 }}>
          이 기능은 현재 개발 중입니다. 곧 출시됩니다!
        </p>
        <div className="badge badge-info" style={{ marginTop: 16, fontSize: '0.8rem', padding: '4px 12px' }}>
          Coming Soon
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [activePage, setActivePage] = useState('dashboard');
  const { t } = useI18n();

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
        return <ComingSoonPage title={t('nav.portfolio')} icon={PieChart} />;
      case 'trading':
        return <TradingPanel />;
      case 'settings':
        return <ComingSoonPage title={t('nav.settings')} icon={Settings} />;
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
