/**
 * Modelin - 퀀트 투자 플랫폼
 *
 * 메인 앱 컴포넌트. 사이드바 네비게이션 + 페이지 라우팅.
 */
import { Component, lazy, Suspense, useState, type ErrorInfo, type ReactNode } from 'react';
import Sidebar from './components/Sidebar';
import HeaderBar from './components/HeaderBar';

function PageFallback() {
  return <div className="page-content"><div className="loading-panel" role="status">화면을 불러오는 중...</div></div>;
}

interface ErrorBoundaryProps { children: ReactNode }
interface ErrorBoundaryState { hasError: boolean }

class PageErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Modelin page render failed', error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="page-content">
        <div className="error-boundary" role="alert">
          <h2>화면을 표시하지 못했습니다.</h2>
          <p>일시적인 화면 오류입니다. 다시 시도하거나 다른 메뉴를 선택해주세요.</p>
          <button className="btn btn-primary" onClick={this.handleRetry}>다시 시도</button>
        </div>
      </div>
    );
  }
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
        <PageErrorBoundary>
          <Suspense fallback={<PageFallback />}>
            {renderPage()}
          </Suspense>
        </PageErrorBoundary>
      </main>
    </div>
  );
}
